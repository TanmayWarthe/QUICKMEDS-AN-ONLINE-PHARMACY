from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import UserProfile
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Product, CartItem, Cart, Category
from django.db.models import Q
import json
from django.views.decorators.csrf import csrf_exempt

def search_products(request):
    query = request.GET.get('q', '')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if is_ajax:
        suggestions = []
        if query:
            products = Product.objects.filter(
                Q(name__icontains=query) |
                Q(category__name__icontains=query) |
                Q(description__icontains=query)
            ).distinct()[:5]
            
            categories = Category.objects.filter(name__icontains=query)[:3]
            
            for product in products:
                suggestions.append({
                    'type': 'product',
                    'id': product.id,
                    'name': product.name,
                    'category': product.category.name,
                    'price': str(product.price),
                    'image_url': product.image.url if product.image else '/static/img/medicines-icon.png'
                })
            
            for category in categories:
                suggestions.append({
                    'type': 'category',
                    'id': category.id,
                    'name': category.name,
                    'count': category.products.count()
                })
        
        return JsonResponse({'suggestions': suggestions})
    
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(category__name__icontains=query) |
            Q(description__icontains=query)
        ).distinct().select_related('category')
        
        categories = Category.objects.filter(
            Q(name__icontains=query) |
            Q(products__name__icontains=query)
        ).distinct()
    else:
        products = Product.objects.none()
        categories = Category.objects.none()
    
    context = {
        'products': products,
        'categories': categories,
        'query': query,
        'cart_count': get_cart_count(request),
        'total_results': products.count()
    }
    return render(request, 'search_results.html', context)

def base(request):
    return render(request, 'base.html')

def home(request):
    return render(request, 'home.html')

def shop_view(request):
    product_id = request.GET.get('product_id')
    if not product_id:
        messages.error(request, 'No product selected')
        return redirect('product')
        
    try:
        product = Product.objects.get(id=product_id)
        if not product.image:
            product.image_url = '/static/img/medicines-icon.png'
        else:
            product.image_url = product.image.url
            
        context = {
            'product': product,
            'cart_count': get_cart_count(request)
        }
        return render(request, 'shop.html', context)
    except Product.DoesNotExist:
        messages.error(request, 'Product not found')
        return redirect('product')
    except Exception as e:
        messages.error(request, f'Error loading product: {str(e)}')
        return redirect('product')

def about_view(request):
    context = {
        'cart_count': get_cart_count(request)
    }
    return render(request, 'about.html', context)

def get_cart_count(request):
    if request.user.is_authenticated:
        return CartItem.objects.filter(cart__user=request.user).count()
    return 0

def product_view(request):
    categories = Category.objects.prefetch_related('products').all()
    
    # Debug information
    print("Number of categories:", categories.count())
    for category in categories:
        print(f"Category: {category.name}")
        print(f"Number of products: {category.products.count()}")
        for product in category.products.all():
            print(f"- {product.name}: ₹{product.price}")
    
    context = {
        'categories': categories,
        'cart_count': get_cart_count(request)
    }
    return render(request, 'product.html', context)

def register(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if not all([name, email, password]):
            messages.error(request, 'Please fill in all fields.')
            return redirect('login')
            
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
            return redirect('login')
            
        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return redirect('login')
            
        try:
            # Create user
            username = email.split('@')[0]  # Generate username from email
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=name.split()[0],
                last_name=' '.join(name.split()[1:]) if len(name.split()) > 1 else ''
            )
            
            # Create user profile
            UserProfile.objects.create(user=user)
            
            messages.success(request, 'Account created successfully! Please login.')
            return redirect('login')
            
        except Exception as e:
            messages.error(request, 'An error occurred during registration. Please try again.')
            return redirect('login')
            
    return redirect('login')

def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if not email or not password:
            messages.error(request, 'Please provide both email and password.')
            return redirect('login')
            
        try:
            user = User.objects.get(email=email)
            user = authenticate(request, username=user.username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, 'Successfully logged in!')
                return redirect('home')
            else:
                messages.error(request, 'Invalid email or password.')
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email.')
        
        return redirect('login')
        
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully!')
    return redirect('login')

@login_required
def profile_view(request):
    context = {
        'cart_count': get_cart_count(request)
    }
    return render(request, 'profile.html', context)

@login_required
def add_to_cart(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            product_id = data.get('product_id')
            quantity = int(data.get('quantity', 1))
            
            if quantity < 1:
                return JsonResponse({'success': False, 'error': 'Quantity must be at least 1'})
                
            product = Product.objects.get(id=product_id)
            cart, created = Cart.objects.get_or_create(user=request.user)
            
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                product=product,
                defaults={'quantity': quantity}
            )
            
            if not created:
                cart_item.quantity += quantity
                cart_item.save()
            
            cart_count = get_cart_count(request)
            
            return JsonResponse({
                'success': True,
                'message': f'Added {quantity} {product.name} to cart',
                'cart_count': cart_count
            })
            
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Product not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
            
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def cart_view(request):
    try:
        cart = Cart.objects.get(user=request.user)
        cart_items = cart.cartitem_set.select_related('product').all()
    except Cart.DoesNotExist:
        cart_items = []
        cart = None
    
    context = {
        'cart_items': cart_items,
        'cart': cart,
        'cart_count': get_cart_count(request)
    }
    return render(request, 'cart.html', context)

@login_required
def update_cart_item(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            item_id = data.get('item_id')
            quantity = int(data.get('quantity', 1))
            
            if quantity < 1:
                return JsonResponse({'success': False, 'error': 'Quantity must be at least 1'})
                
            cart_item = CartItem.objects.get(
                id=item_id,
                cart__user=request.user
            )
            
            cart_item.quantity = quantity
            cart_item.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Cart updated successfully',
                'new_quantity': quantity,
                'new_total': cart_item.get_total()
            })
            
        except CartItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Item not found in cart'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
            
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def remove_cart_item(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            item_id = data.get('item_id')
            
            cart_item = CartItem.objects.get(
                id=item_id,
                cart__user=request.user
            )
            cart_item.delete()
            
            cart_count = get_cart_count(request)
            
            return JsonResponse({
                'success': True,
                'message': 'Item removed from cart',
                'cart_count': cart_count
            })
            
        except CartItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Item not found in cart'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
            
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def showEmptyCartMessage():
    return JsonResponse({
        'success': False,
        'error': 'Your cart is empty'
    })

@login_required
def checkout_view(request):
    try:
        cart = Cart.objects.get(user=request.user)
        cart_items = cart.cartitem_set.select_related('product').all()
        
        if not cart_items:
            messages.warning(request, 'Your cart is empty. Please add items to your cart before proceeding to checkout.')
            return redirect('cart')
        
    except Cart.DoesNotExist:
        messages.warning(request, 'Your cart is empty. Please add items to your cart before proceeding to checkout.')
        return redirect('cart')
    
    context = {
        'cart_items': cart_items,
        'cart': cart,
        'cart_count': get_cart_count(request)
    }
    
    return render(request, 'checkout.html', context)
